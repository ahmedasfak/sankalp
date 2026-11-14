# Setup 2: connect to the model
import os, re, json, time, operator
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()
llm = ChatOpenAI(api_key=os.getenv("OPENROUTE_API_KEY"),
             openai_api_base="https://openrouter.ai/api/v1",
                 model_name="openai/gpt-4o-mini" # Or any model on OpenRouter
                 
                 )
#print("Model ready:", llm.model_name)
#print(llm.invoke("what is the capital of india"))