from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from fastapi import HTTPException
import os
import uuid
import re
from send_email import send_approval_email
from db.async_sql import save_request
from schemas.users import ChatState, CategorizeQuery
from flow_utils import normalize_category, should_route_to_answer
load_dotenv()


groq_api = os.getenv("GROQ_API_KEY")
REVIEWER_EMAIL = os.getenv("REVIEWER_EMAIL", "mnandanwar0@gmail.com")

llm = ChatGroq(model="qwen/qwen3.6-27b", api_key=groq_api)
categorize_llm = llm.with_structured_output(CategorizeQuery)



async def classify_query(state: ChatState):
    prompt = f"""
    Classify the following query as safe or unsafe. If the user wants to know something harmful or related to danger, categorize it as UNSAFE.
    Query:
    {state['query']}
    """
    
    result = await categorize_llm.ainvoke(prompt)
    category = getattr(result, "category", None)
    return {"category": normalize_category(category)}


async def answer_llm(state: ChatState):
    response = await llm.ainvoke(state["query"])
    content = response.content if hasattr(response, "content") else str(response)
    return {"answer": content,'status':'Approved'}


async def human_review(state: ChatState):
    approval_id = str(uuid.uuid4())
    await save_request(
        approval_id=approval_id,
        user_id=state["user_id"],
        query=state["query"],
        status="PENDING")

    email_note = "An email has been sent to the reviewer."
    try:
        await send_approval_email(
            receiver_email=REVIEWER_EMAIL,
            approval_id=approval_id,
            query=state["query"],
        )

    except Exception as exc:
        print(f"Approval email failed: {exc}")
        email_note = f"Approval request saved, but email could not be sent: {exc}"

    return {
        "status": "PENDING_APPROVAL",
        "approval_id": approval_id,
        "message": (
            "Your request requires human approval. "
            f"{email_note} You will be notified here once it is reviewed."
        ),
    }


def router(state: ChatState):
    if should_route_to_answer(state.get("category")):
        return "answer"
    return "review"


def extract_response(state: ChatState) -> str:
    print(state['status'])
    if state.get("status") == "PENDING_APPROVAL":
        return state.get(
            "message",
            "Your request requires human approval. An email has been sent to the reviewer.",
        )

    answer = state.get("answer")
    if answer is None:
        return "No response generated."

    if isinstance(answer, AIMessage):
        return answer.content
    return str(answer)


def define_workflow(saver):
    try:
        graph = StateGraph(ChatState)

        graph.add_node("classifier", classify_query)
        graph.add_node("answer", answer_llm)
        graph.add_node("human_review", human_review)

        graph.add_edge(START, "classifier")
        graph.add_conditional_edges(
            "classifier",
            router,
            {
                "answer": "answer",
                "review": "human_review",
            },
        )
        graph.add_edge("answer", END)
        graph.add_edge("human_review", END)

        return graph.compile(checkpointer=saver)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def execute_approved_request(request):
    result = await answer_llm({"query": request["query"]})
    return {"answer": result["answer"]}



def format_qa_history(checkpoints):
    queries = {}

    for checkpoint in checkpoints:
        state = checkpoint.values

        query = state.get("query")
        answer = state.get("answer")
        print('query:',query)
        print('answer:',answer)
        if not query:
            continue

        # Initialize the query the first time we see it
        if query not in queries:
            queries[query] = {
                "query": query,
                "answer": None
            }

        # The answer can appear in a later checkpoint
        if answer:
            # Remove <think>...</think> from the answer
            answer = re.sub(
                r"<think>.*?</think>\s*",
                "",
                answer,
                flags=re.DOTALL
            ).strip()

            queries[query]["answer"] = answer

    # Convert to the required Q/A format
    qa_pairs = []

    for item in queries.values():
        qa_pairs.append({
            "type": "que",
            "content": item["query"]
        })

        if item["answer"]:
            qa_pairs.append({
                "type": "ans",
                "content": item["answer"]
            })

    return qa_pairs
