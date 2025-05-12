import sys
import os
from flask import Flask, render_template, request, jsonify
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage # Import message types

# Add project root to Python path to allow importing agent
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the compiled LangGraph app
try:
    from agent.graph import app as langgraph_app
    print("LangGraph app imported successfully.")
except ImportError as e:
    print(f"Error importing LangGraph app: {e}")
    langgraph_app = None
except Exception as e:
    print(f"An unexpected error occurred during import: {e}")
    langgraph_app = None

flask_app = Flask(__name__)

# In-memory store for conversation history - Use actual Message objects now
conversation_history: list = [] 

@flask_app.route("/")
def index():
    """Serves the main chat interface."""
    global conversation_history
    conversation_history = [] # Reset history on page load
    print("Rendering index page and resetting history.")
    return render_template("index.html")

@flask_app.route("/chat", methods=["POST"])
def chat():
    """Handles chat messages and interacts with the LangGraph agent."""
    global conversation_history
    
    if not langgraph_app:
         print("Error: LangGraph app not loaded.")
         return jsonify({"error": "Agent backend not available"}), 500

    try:
        user_message_content = request.json["message"]
        print(f"Received message: {user_message_content}")
        user_message = HumanMessage(content=user_message_content)
        history_before_invoke = list(conversation_history)
        current_input = {"messages": history_before_invoke + [user_message]}

        print(f"Invoking agent with {len(current_input['messages'])} history entries.")
        final_state = langgraph_app.invoke(current_input)
        
        if not (isinstance(final_state, dict) and "messages" in final_state):
             print(f"Unexpected final state format: {final_state}")
             return jsonify({"error": "Unexpected response format from agent"}), 500

        all_messages = final_state["messages"]
        agent_response_message = all_messages[-1]
        agent_response_content = getattr(agent_response_message, 'content', str(agent_response_message))

        # Determine Tool Usage and Response Type for this Turn
        response_type = 'general_knowledge' # Default
        tool_names_invoked = [] # New: list of names
        messages_this_turn = all_messages[len(history_before_invoke):]
        last_tool_outcome = None # Track outcome related to the *last* tool message

        for i, msg in enumerate(messages_this_turn):
            if isinstance(msg, AIMessage) and getattr(msg, 'tool_calls', None) and msg.tool_calls:
                 # Add all tool calls from this AIMessage
                 for tool_call in msg.tool_calls:
                    tool_name = tool_call.get('name')
                    if tool_name and tool_name not in tool_names_invoked: # Avoid duplicates if model calls same tool multiple times weirdly
                        tool_names_invoked.append(tool_name)
                 # Check if the *next* message is a ToolMessage to determine outcome *for this specific AI message turn*
                 if (i + 1 < len(messages_this_turn) and isinstance(messages_this_turn[i+1], ToolMessage)):
                     last_tool_outcome = 'tool_success' if not messages_this_turn[i+1].content.startswith("Error:") else 'tool_failure'
                 else:
                     last_tool_outcome = 'tool_invocation_unknown_outcome'
            elif isinstance(msg, ToolMessage) and not tool_names_invoked: # If a tool message appears without a preceding AIMessage call in this turn
                 tool_names_invoked.append("Unknown")
                 last_tool_outcome = 'tool_success' if not msg.content.startswith("Error:") else 'tool_failure'

        # Determine overall response_type based on whether any tools were invoked and the outcome of the last one
        if tool_names_invoked:
            response_type = last_tool_outcome or 'tool_invocation_unknown_outcome' # Use the determined outcome

        print(f"Response type: {response_type}, Tools invoked: {tool_names_invoked}")

        # Update conversation history
        conversation_history = all_messages

        print(f"Agent response text: {agent_response_content}")
        print(f"History length now: {len(conversation_history)}")

        return jsonify({
            "response_text": agent_response_content,
            "response_type": response_type,
            "tool_names": tool_names_invoked
        })

    except Exception as e:
        print(f"Error during chat processing: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"An internal error occurred: {e}", "response_type": "error"}), 500

@flask_app.route("/clear", methods=["POST"])
def clear_chat():
    """Clears the server-side conversation history."""
    global conversation_history
    conversation_history = []
    print("Server-side conversation history cleared.")
    return jsonify({"status": "cleared"})

if __name__ == "__main__":
    print("Starting Flask app...")
    # Ensure template and static folders exist
    if not os.path.exists('app/templates'):
        os.makedirs('app/templates')
    if not os.path.exists('app/static'):
        os.makedirs('app/static')
    flask_app.run(debug=True, host='0.0.0.0', port=5001) # Use port 5001 to avoid conflicts 