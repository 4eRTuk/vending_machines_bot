from dotenv import load_dotenv

import os


load_dotenv()


class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    DATABASE_URL = 'sqlite:///vending.db'
