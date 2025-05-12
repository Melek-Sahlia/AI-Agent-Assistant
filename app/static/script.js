document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const clearChatButton = document.getElementById('clear-chat-button');

    // Simple function to generate a consistent class name from a tool name
    function getToolClass(toolName) {
        if (!toolName) return '';
        // Basic normalization: lower case, replace underscore with hyphen
        const normalized = toolName.toLowerCase().replace(/_/g, '-');
        // You could add more sophisticated hashing or mapping for more colors
        return `tool-${normalized}`;
    }

    // Function to add a message to the chat box
    function addMessage(data, type) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', `${type}-message`);

        if (type === 'assistant' && typeof data === 'object' && data !== null) {
            // Handle structured response from backend

            // Create container for badges
            const badgesContainer = document.createElement('div');
            badgesContainer.style.marginBottom = '5px'; // Add space below badges

            if (data.response_type && data.response_type !== 'general_knowledge') {
                const toolNames = data.tool_names || []; // Expecting an array now
                const isFailure = data.response_type === 'tool_failure';

                toolNames.forEach(toolName => {
                    const badge = document.createElement('span');
                    const toolClass = getToolClass(toolName);
                    badge.classList.add('badge');
                    // Apply general success/failure class or tool-specific class
                    if (isFailure) {
                        badge.classList.add('badge-tool_failure');
                    } else if (toolClass) {
                        badge.classList.add(toolClass); // Use specific tool color
                    } else {
                        badge.classList.add('badge-tool_success'); // Fallback success color
                    }
                    
                    if (toolClass) {
                         badge.classList.add(toolClass); // Ensure tool class is present for styling
                    }

                    badge.textContent = toolName; // Removed "Tool: " prefix
                    if (isFailure) {
                       // Maybe add indicator only if it's the *last* tool and failed?
                       // For now, keep it simple: failure color applies if overall outcome is failure.
                    }
                    badgesContainer.appendChild(badge); 
                });
            }
            
            // Add badges container only if it has badges
            if (badgesContainer.hasChildNodes()) {
                messageDiv.appendChild(badgesContainer);
            }

            // Add main response text after the badges (if any)
             // Render the response text as Markdown
             const responseHtml = marked.parse(data.response_text || "(No response text)");
             const textSpan = document.createElement('span');
             textSpan.innerHTML = responseHtml; // Use innerHTML as marked.parse returns HTML string
             messageDiv.appendChild(textSpan);
            
        } else {
            // Handle user messages or simple assistant messages (like 'thinking')
            messageDiv.textContent = data; 
        }

        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // Function to clear the chat interface and backend history
    async function clearChat() {
        // Clear the visual chat box
        chatBox.innerHTML = ''; 
        
        // Add the initial greeting message back
        addMessage('Hello! How can I help you today?', 'assistant');

        // Call the backend to clear its history
        try {
            const response = await fetch('/clear', { method: 'POST' });
            if (!response.ok) {
                console.error("Failed to clear server-side history:", response.statusText);
                addMessage("Error clearing server history.", 'assistant'); // Optional: notify user
            }
        } catch (error) {
            console.error("Error calling /clear endpoint:", error);
            addMessage("Error clearing server history.", 'assistant'); // Optional: notify user
        }

        // Re-focus input
        userInput.focus();
    }

    // Function to handle sending a message
    async function sendMessage() {
        const messageText = userInput.value.trim();
        if (!messageText) return;

        addMessage(messageText, 'user');
        userInput.value = ''; 
        userInput.disabled = true;
        sendButton.disabled = true;
        addMessage("Agent thinking...", 'assistant'); 

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageText }),
            });

            const thinkingMessage = chatBox.querySelector('.assistant-message:last-child');
            if (thinkingMessage && thinkingMessage.textContent === "Agent thinking...") {
                chatBox.removeChild(thinkingMessage);
            }

            const data = await response.json(); // Assume response is always JSON now

            if (!response.ok) {
                addMessage({ response_text: `Error: ${data.error || response.statusText}`, response_type: 'error' }, 'assistant');
            } else {
                addMessage(data, 'assistant'); // Pass the whole data object
            }

        } catch (error) {
            const thinkingMessage = chatBox.querySelector('.assistant-message:last-child');
            if (thinkingMessage && thinkingMessage.textContent === "Agent thinking...") {
                chatBox.removeChild(thinkingMessage);
            }
            console.error("Fetch error:", error);
            addMessage({ response_text: "Error sending message. Check console.", response_type: 'error' }, 'assistant');
        } finally {
             userInput.disabled = false;
             sendButton.disabled = false;
             userInput.focus();
        }
    }

    // Event listeners
    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            sendMessage();
        }
    });

    // Event listener for the clear chat button
    clearChatButton.addEventListener('click', clearChat);
}); 