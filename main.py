from fastapi import FastAPI
from payments import router as payments_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Conference Registration API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","https://saigangapanakeia.com"],  # React frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(payments_router, prefix="/payments", tags=["Payments"])
