import os
from typing import AsyncGenerator
from dotenv import load_dotenv
from pymongo import MongoClient
from contextlib import asynccontextmanager, contextmanager
from fastapi import FastAPI

load_dotenv() # load environment variables from .env file


# for the database connection
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Start the database connection
    print(app)
    print("MongoBD startup")
    mongo_connection = connect_to_db()
    print(mongo_connection)
    app.db = next(mongo_connection)
    app.client = app.db.client

    """ app.client = mongo_connection[0]
    app.db = mongo_connection[1] """
    yield
    # Close the database connection
    await shutdown_db_client(app)

# method to connect to the MongoDb Connection for dependency injection
def connect_to_db():
    with MongoClient(os.getenv('MONGO_DB_CONNECTION_STRING')) as client:
        db = client.get_database(os.getenv('MONGO_DB_NAME'))
        print(client)
        print(db)
        print("MongoDB connected.")
        yield db



# method to close the database connection
async def shutdown_db_client(app):
    app.client.close()
    print("Database disconnected.")