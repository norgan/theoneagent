document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("chat-form");
    const input = document.getElementById("message-input");
    const chatBox = document.getElementById("chat-box");
    const apiKey = "your-agent-secret"; // Ensure this is your actual IKIRONE_API_KEY from .env

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const userMessage = input.value.trim();
        if (!userMessage) return;

        addMessage(userMessage, "user");
        input.value = "";
        
        try {
            const response = await fetch("/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-KEY": apiKey
                },
                body: JSON.stringify({ message: userMessage })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || "An unknown error occurred.");
            }

            const data = await response.json();
            addMessage(data.response, "agent");

        } catch (error) {
            addMessage(`**Error:** ${error.message}`, "agent");
        }
    });

    function addMessage(text, sender) {
        const messageElement = document.createElement("div");
        messageElement.classList.add("message", `${sender}-message`);
        
        const p = document.createElement("div"); // Use a div to better contain complex HTML
        
        if (sender === 'agent') {
            // If the message is from the agent, parse it as Markdown
            p.innerHTML = marked.parse(text);
        } else {
            // Otherwise, treat it as plain text
            p.textContent = text;
        }

        messageElement.appendChild(p);
        chatBox.appendChild(messageElement);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
});
