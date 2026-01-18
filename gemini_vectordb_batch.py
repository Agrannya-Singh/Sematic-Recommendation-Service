import pandas as pd
import google.generativeai as genai
from pinecone import Pinecone, ServerlessSpec
import time
import os
from tqdm import tqdm

# --- CONFIG ---
# --- KEYS ---
#add pinecone and gemini key here to work :)
INDEX_NAME = "screenscout-google-v1"

# 1. Setup Services
genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)

# 2. Create Index (768 Dimensions for Google)
if INDEX_NAME not in pc.list_indexes().names():
    pc.create_index(
        name=INDEX_NAME,
        dimension=768,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
index = pc.Index(INDEX_NAME)

# 3. Load & Clean Data
print("Loading Data...")
df = pd.read_csv("movies_metadata.csv", low_memory=False)

# Clean Data
df = df.dropna(subset=['overview', 'poster_path', 'title'])
df = df[df['original_language'] == 'en']

# --- CRITICAL FIX: Reset Index to avoid 'IndexError' ---
df = df.reset_index(drop=True)
print(f"Total Movies to Ingest: {len(df)}")

# 4. Batch Processing Function
BATCH_SIZE = 100  # Google allows up to 100-250 per call

def generate_embeddings_batch(texts):
    # Google API expects a list of strings
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=texts,
        task_type="retrieval_document"
    )
    return result['embedding']

# 5. The Main Loop
vectors_to_upsert = []
print("Starting Batch Ingestion...")

# Iterate through the DataFrame in chunks of BATCH_SIZE
for i in tqdm(range(0, len(df), BATCH_SIZE)):
    try:
        # Slice the dataframe
        batch = df.iloc[i : i + BATCH_SIZE]
        
        # Prepare Texts (Title + Overview)
        batch_texts = (batch['title'] + ": " + batch['overview']).tolist()
        
        # 1. Get Embeddings (1 API Call for 100 Movies)
        embeddings = generate_embeddings_batch(batch_texts)
        
        # 2. Prepare Vectors for Pinecone
        for j, (idx, row) in enumerate(batch.iterrows()):
            metadata = {
                "title": str(row['title']),
                "poster_path": str(row['poster_path']),
                "overview": str(row['overview'])[:500],
                "release_date": str(row['release_date']),
                "vote_average": str(row['vote_average'])
            }
            # ID must be string
            vectors_to_upsert.append((str(row['id']), embeddings[j], metadata))
        
        # 3. Upsert to Pinecone
        index.upsert(vectors_to_upsert)
        vectors_to_upsert = [] # Clear buffer
        
        # Sleep slightly to be kind to the API
        time.sleep(1)

    except Exception as e:
        print(f"Error in batch starting at {i}: {e}")
        time.sleep(5) # Cool down if error occurs
        continue

print("Ingestion Complete! You survived the API limits.")
