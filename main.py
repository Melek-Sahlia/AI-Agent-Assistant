import sys
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Load environment variables first
load_dotenv()

# Import the compiled agent graph (ensure env vars are loaded before this)
from agent.graph import app

def main():
    print("Welcome to the AI Agent!")
    print("Type 'exit' or 'quit' to end the conversation.")

    # Define the system prompt
    system_message = SystemMessage(content="You are a helpful AI assistant equipped with several tools: google_search, browse_website, read_email, and send_email. Use these tools when appropriate to answer the user's request. Think step-by-step about whether a tool is needed.")

    # Maintain conversation history, starting with the system message
    messages = [system_message]

    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ['exit', 'quit']:
                print("AI Agent shutting down. Goodbye!")
                break

            if not user_input:
                continue

            # Append the user message to the history
            messages.append(HumanMessage(content=user_input))

            # Invoke the agent graph
            # The input includes the system message and conversation history
            print("\nAI Agent thinking...") # Indicate activity
            # Use stream for more detailed output during execution (optional)
            # for event in app.stream({"messages": messages}):
            #     for key, value in event.items():
            #         print(f"--- Event from node: {key} ---")
            #         # print(value) # Can be verbose
            #     print("---")
            
            # Use invoke for the final result
            final_state = app.invoke({"messages": messages})
            
            # The final response is the last message in the state
            response_message = final_state['messages'][-1]

            # Update history with the agent's final response
            if isinstance(response_message, AIMessage):
                 # Don't add the system message repeatedly to the history
                 messages.append(response_message) 
                 print(f"\nAgent: {response_message.content}")
            else:
                 # Handle cases where the last message isn't from the AI (e.g., tool error)
                 print(f"\nAgent: (No direct response, last event was: {type(response_message).__name__})")
                 # We might still want to append other message types to history if needed
                 # Don't add the system message repeatedly to the history
                 messages.append(response_message) 

        except EOFError: # Handle Ctrl+D
             print("\nAI Agent shutting down. Goodbye!")
             break
        except KeyboardInterrupt: # Handle Ctrl+C
            print("\nInterrupt received. Shutting down...")
            break
        except Exception as e:
            print(f"\nAn error occurred: {e}")
            # Optionally decide whether to break or continue on error
            # break

if __name__ == "__main__":
    main() 