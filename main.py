from fastapi import FastAPI

app = FastAPI()

@app.get('/')
def root():
    return {'status': 'VyaparAI M1 running'}
