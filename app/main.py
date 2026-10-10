
from fastapi import FastAPI

app = FastAPI(
    title="OpsPilot",
    description="Evidence-driven AI incident investigation",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "opspilot-api",
        "version": "0.1.0",
    }