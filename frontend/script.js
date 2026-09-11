const API_URL = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws";

let chatSocket = null;

function getToken() {
    return localStorage.getItem("access_token");
}


function connectWebSocket() {
    const token = getToken();
    if (!token) {
        return;
    }

    if (chatSocket && chatSocket.readyState <= WebSocket.OPEN) {
        return;
    }

    chatSocket = new WebSocket(`${WS_URL}?token=${encodeURIComponent(token)}`);

    chatSocket.onopen = () => {
        console.log("WebSocket connected");
    };

    chatSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const responseEl = document.getElementById("response");
        console.warn(data)
        if (!responseEl) {
            return;
        }

        if (data.type === "approval_completed") {
            responseEl.innerHTML = `
                <p><strong>Approved query:</strong> ${escapeHtml(data.query)}</p>
                <p><strong>Answer:</strong> ${escapeHtml(data.answer)}</p>
            `;
        } else if (data.type === "approval_rejected") {
            responseEl.innerHTML = `
            <div class="chat-message rejected">

                <h3>Request Rejected</h3>

                <p><strong>Approval ID:</strong> ${escapeHtml(data.approval_id)}</p>

                <p><strong>Query:</strong> ${escapeHtml(data.query)}</p>

                <p><strong>Reason:</strong> ${escapeHtml(data.reason)}</p>

            </div>
        `;
        }
    };

    chatSocket.onclose = () => {
        console.log("WebSocket disconnected, reconnecting in 3s...");
        chatSocket = null;
        setTimeout(connectWebSocket, 3000);
    };

    chatSocket.onerror = (error) => {
        console.error("WebSocket error:", error);
    };
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
}

function initChatPage() {
    if (!getToken()) {
        window.location.href = "login.html";
        return;
    }
    connectWebSocket();
}

// ============ REGISTER API ============
async function register() {
    const name = document.getElementById("name").value.trim();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value.trim();

    if (!name || !email || !password) {
        alert("Please fill all fields");
        return;
    }

    try {
        const response = await fetch(`${API_URL}/register`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ name, email, password }),
        });

        const data = await response.json();
        console.log("Register response:", data);

        if (response.ok) {
            alert(data.message);
            window.location.href = "login.html";
        } else {
            alert(data.detail || data.message || "Registration failed");
        }
    } catch (error) {
        console.error("Registration error:", error);
        alert("Server error: " + error.message);
    }
}

// ============ LOGIN API ============
async function login() {
    const email = document.getElementById("login_email").value.trim();
    const password = document.getElementById("login_password").value.trim();

    if (!email || !password) {
        alert("Please enter email and password");
        return;
    }

    try {
        const response = await fetch(`${API_URL}/login`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ email, password }),
        });

        const data = await response.json();
        console.log("Login response:", data);

        if (response.ok && data.access_token) {
            localStorage.setItem("access_token", data.access_token);
            alert(data.message || "Login successful");
            window.location.href = "chat.html";
        } else {
            alert(data.detail || data.message || "Login failed");
        }
    } catch (error) {
        console.error("Login error:", error);
        alert("Server error: " + error.message);
    }
}

// ============ CHAT API ============
async function sendMessage() {
    const message = document.getElementById("question").value.trim();
    const token = getToken();

    if (!message) {
        alert("Please enter a message");
        return;
    }

    if (!token) {
        alert("You are not authenticated. Please login first.");
        window.location.href = "login.html";
        return;
    }

    const responseEl = document.getElementById("response");
    responseEl.innerHTML = "<em>Thinking...</em>";

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ message }),
        });

        const data = await response.json();
        console.log("Chat response:", data);

        if (response.ok) {
            responseEl.innerHTML = escapeHtml(data.answer);
            document.getElementById("question").value = "";
        } else {
            responseEl.innerHTML = "";
            alert(data.detail || "Error sending message");
        }
    } catch (error) {
        console.error("Chat error:", error);
        responseEl.innerHTML = "";
        alert("Server error: " + error.message);
    }
}

// ============ LOGOUT ============
function logout() {
    if (chatSocket) {
        chatSocket.close();
        chatSocket = null;
    }
    localStorage.removeItem("access_token");
    alert("Logged out successfully");
    window.location.href = "login.html";
}

if (document.getElementById("response")) {
    initChatPage();
}
