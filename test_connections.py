from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
result = client.table('businesses').select('*').execute()
print('Supabase OK:', result.data)
