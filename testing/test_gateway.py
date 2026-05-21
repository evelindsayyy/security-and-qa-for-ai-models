from dotenv import load_dotenv
from openai import OpenAI

# load your local .env
load_dotenv()

def run_simple_test():
    # initialize connection to the gateway proxy
    client = OpenAI()
    
    print("Sending request to Duke AI Gateway using GPT 4.1 Mini...")

    response = client.chat.completions.create(
        model="GPT 4.1 Mini",  
        messages=[
            {
                "role": "system", 
                "content": "You are a concise data assistant. Classify the sentiment of text as Positive, Negative, or Neutral."
            },
            {
                "role": "user", 
                "content": "For a first-time director, the movie was surprisingly decent—though that isn't saying much."
            }
        ]
    )
    
    # print just the answer
    print("\n[AI Response]:")
    print(response.choices[0].message.content)

if __name__ == "__main__":
    run_simple_test()