import os
import operator
from typing import TypedDict, List
import logging

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# Import agent state and tools
from .state import AgentState
from tools.search import search_tool
from tools.browser import browse_tool
from tools.gmail import read_email_tool, send_email_tool

# --- Setup --- 

# Load environment variables
load_dotenv()

# Check for Gemini API Key
if not os.getenv("GEMINI_API_KEY"):
    raise ValueError("GEMINI_API_KEY environment variable not set.")

# Initialize the LLM (Gemini)
# Using gemini-1.5-flash-latest for potentially faster responses and function calling support
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest", temperature=0, convert_system_message_to_human=True)

# List of tools
tools = [search_tool, browse_tool, read_email_tool, send_email_tool]

# Define a more directive system prompt
system_prompt = ("""
You are a helpful AI assistant designed to integrate with external tools.
Your available tools are: google_search, browse_website, read_email, send_email.

**Instructions:**
1.  Analyze the user's request carefully, paying attention to context from previous messages (e.g., if the user says "it", figure out what "it" refers to).
2.  Determine if any of your available tools can fulfill the request. Break down multi-step requests into sequential tool calls if necessary.
3.  **If a tool is available for the task, you MUST attempt to use it.** Do not claim you cannot perform the action if a relevant tool exists.
4.  Think step-by-step before deciding which tool to use and what arguments to provide. Construct the arguments precisely according to the tool's requirements.
5.  If multiple tools are needed (e.g., browse a website then send its content via email), plan and execute the steps sequentially. Use the output from one step as input for the next.
6.  If no tool is suitable, or if a tool fails unexpectedly after you attempt to use it, explain the situation clearly.
7.  If unsure about context or the required action, ask the user for clarification.
""")

# Setup logging (add if not present)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Node Definitions --- 

def should_continue(state: AgentState) -> str:
    """ Determines whether to continue the loop or end."""
    messages = state['messages']
    last_message = messages[-1]
    # If there are no tool calls, stop.
    # Handle cases where the last message might be a ToolMessage if an error occurred in ToolNode
    if not isinstance(last_message, AIMessage) or not getattr(last_message, 'tool_calls', None):
        return "end"
    # Otherwise if there are tool calls, continue.
    else:
        # We have tool calls, tell the graph to continue to the action node
        print(f"Continuing with tool calls: {last_message.tool_calls}") # Add print statement
        return "continue"

def call_model(state: AgentState):
    """ Calls the LLM with the current state to decide the next step."""
    # Prepend the system prompt to the messages if it's not already there
    # This ensures the prompt is always considered, especially in LangGraph state handling
    messages = state['messages']
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt)] + messages
    
    # Bind tools to the LLM
    model_with_tools = llm.bind_tools(tools)

    print(f"\n--- Calling Model with {len(messages)} messages ---")
    # --- DEBUG: Print the messages being sent ---
    print("--- Message History Sent to Model: ---")
    for i, msg in enumerate(messages):
        print(f"[{i}] Type: {type(msg).__name__}")
        try:
            print(f"    Content: {msg.content}")
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                print(f"    Tool Calls: {msg.tool_calls}")
            if hasattr(msg, 'tool_call_id') and msg.tool_call_id:
                 print(f"    Tool Call ID: {msg.tool_call_id}")
        except Exception as e:
            print(f"    Error accessing message attributes: {e}")
            print(f"    Raw Message Obj: {msg}") # Print raw object if error
    print("------------------------------------")
    # ------------------------------------------

    # Passing original messages, bind_tools handles the formatting implicitly for many models
    try:
        response = model_with_tools.invoke(messages)
    except Exception as e:
         print(f"--- ERROR DURING MODEL INVOCATION ---")
         print(f"Error: {e}")
         # Re-raise or return error state? Let's return an error message in the state
         error_content = f"Error calling model: {e}"
         # Avoid breaking graph, return AIMessage with error
         # Important: Make sure this error message also gets added correctly
         return {"messages": [AIMessage(content=error_content)]}

    print(f"--- Model Response --- \n{response}") # Add print statement

    # Ensure the response is always a BaseMessage type AND handle empty content
    if isinstance(response, AIMessage):
        if response.tool_calls and not response.content:
            # Case 1: Tool calls present, content empty -> Add placeholder
            logger.info("AIMessage has tool calls but empty content. Adding placeholder.")
            response.content = "[Deciding which tool to use...]" 
        elif not response.tool_calls and not response.content:
            # Case 2: No tool calls, content empty -> Add different placeholder or handle as error
            logger.warning("AIMessage has no tool calls and no content. Adding placeholder.")
            response.content = "[LLM returned empty response]" # Placeholder for completely empty AI message

    elif isinstance(response.content, str) and not getattr(response, 'tool_calls', None):
         # Case 3: Plain string response -> Wrap in AIMessage
         # Ensure tool_calls exists even if empty (seems needed for some models/versions)
         response = AIMessage(content=response.content, tool_calls=[])
    elif not isinstance(response, BaseMessage):
         # Case 4: Ensure the response is always a BaseMessage type
         response = AIMessage(content=str(response))

    # Append the model's response (AIMessage with potential tool calls) to the state
    # operator.add in AgentState handles the accumulation
    return {"messages": [response]}

# --- Graph Definition --- 

workflow = StateGraph(AgentState)

# Define the nodes
workflow.add_node("agent", call_model)

# Add the ToolNode
tool_node = ToolNode(tools)
workflow.add_node("action", tool_node) 

# Set the entrypoint
workflow.set_entry_point("agent")

# Add conditional edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "action",
        "end": END
    }
)

# Add normal edge from action back to agent
workflow.add_edge('action', 'agent')

# Compile the graph
app = workflow.compile()

print("\nAgent graph compiled successfully using ToolNode!")

# --- Optional: Simple Test (run from main.py later) ---
# if __name__ == '__main__':
#     inputs = {"messages": [HumanMessage(content="What is the latest news about Google Gemini?")]}
#     for output in app.stream(inputs):
#         # stream() yields detailed state updates
#         for key, value in output.items():
#             print(f"Output from node '{key}':")
#             print("---")
#             print(value)
#         print("\n---\n")

#     print("\nFinal State:")
#     final_state = app.invoke(inputs)
#     print(final_state['messages'][-1].content)