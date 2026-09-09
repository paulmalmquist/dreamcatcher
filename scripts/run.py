from pathlib import Path
import os,sys
from dotenv import load_dotenv
root=Path(__file__).resolve().parents[1]
load_dotenv(root/'.env')
sys.path.insert(0,str(root/'backend'))
import uvicorn
if __name__=='__main__':
    uvicorn.run('dreamcatcher.main:app',host=os.getenv('DC_BIND_HOST','127.0.0.1'),port=int(os.getenv('PORT','8000')))
