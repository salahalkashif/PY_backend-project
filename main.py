from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root(name: str):
    return {"message": f"hi {name}"}
