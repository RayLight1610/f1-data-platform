import os

from dotenv import load_dotenv
from sqlalchemy import create_engine


def get_engine():

    load_dotenv()

    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    db = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")

    connection_string = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(connection_string)
    return engine
