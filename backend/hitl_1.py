import os

from dotenv import load_dotenv
from send_email import send_approval_email
from db.sql_query import save_request
from models import *
load_dotenv()
import uuid
from db.sql_query import  save_request
from langchain_groq import ChatGroq


llm = ChatGroq(model="llama-3.1-8b-instant",api_key=os.getenv('GROQ_API_KEY'))

cateorize_llm = llm.with_structured_output(CategorizeQuery)


def classify_query(state: ChatState):

    prompt = f"""
Classify the following query is safe or unsafe. user want to know question which is harmful or related to danger
then categorize.

Categorize the the query.
Query:
{state['query']}
"""
    result = cateorize_llm.invoke(prompt) 
    return {'category': result.category}


def answer_llm(state: ChatState):
    response = llm.invoke(state["query"])
    return {'answer':response.content}


async def human_review(state):
    approval_id = str(uuid.uuid4())
    # Save approval request
    save_request(
        approval_id=approval_id,
        user_id=state["user_id"],
        query=state["query"],
        status="PENDING")

    # Send email
    await send_approval_email(
        receiver_email="mnandanwar0@gmail.com",
        approval_id=approval_id,
        query=state["query"])
    
    return {
        "status": "PENDING_APPROVAL",
        "approval_id": approval_id,
        "message": "Approval request has been sent."
    }


def reject(state):

    state["answer"] = (
        "Your request requires human approval and "
        "has been rejected.")

    return state

