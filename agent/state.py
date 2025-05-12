import operator
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """ Represents the state of our agent graph. """
    messages: Annotated[List[BaseMessage], operator.add] 