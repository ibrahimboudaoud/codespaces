from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymongo import MongoClient
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_transformers.openai_functions import ( create_metadata_tagger)
from langchain_openai import ChatOpenAI

#Load mongoDB book in
loader = PyPDFLoader('/workspaces/codespaces/mongodb.pdf')
pages = loader.load()

# Filter pages (arbitrarly choose 50 words as minimum to filter)
notablePages = []
for page in pages:
    if len(page.page_content) >= 50:
        notablePages.append(page)                          

#Now chunk by paragraph        
text_splitter = RecursiveCharacterTextSplitter(chunk_size = 500, chunk_overlap = 150)

split_docs = text_splitter.split_documents(notablePages)

#Collect more metadeta
schema = {
    "properties" : {
        "title": {"type": "string"},
        "keywords": {"type" : "array", "items":{"type": "string"}},
        "hasCode": {"type": "boolean"} },
        "required": ["title", "keywords", "hasCode"],
    
        }
#llm = ChatOpenAI(open)


