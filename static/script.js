document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("chat-form");
    const input = document.getElementById("message-input");
    const chatBox = document.getElementById("chat-box");
    const apiKey = "No35rg876an!andthisisasecurecode)(*&^%$#@"; // Replace with your actual IKIRONE_API_KEY from .env

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
            addMessage(`Error: ${error.message}`, "agent");
        }
    });

    function addMessage(text, sender) {
        const messageElement = document.createElement("div");
        messageElement.classList.add("message", `${sender}-message`);
        
        const p = document.createElement("p");
        p.textContent = text;
        messageElement.appendChild(p);

        chatBox.appendChild(messageElement);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
});
