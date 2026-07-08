import json

OPENAI_KEY = input("Paste your OpenAI API key: ").strip()

with open("mission_ai_service_account.json", "r") as f:
    data = json.load(f)

print("\nCOPY EVERYTHING BELOW INTO STREAMLIT SECRETS:\n")
print(f'OPENAI_API_KEY = "{OPENAI_KEY}"\n')
print("[gcp_service_account]")

for key, value in data.items():
    if key == "private_key":
        print('private_key = """')
        print(value.strip())
        print('"""')
    else:
        safe_value = str(value).replace('"', '\\"')
        print(f'{key} = "{safe_value}"')