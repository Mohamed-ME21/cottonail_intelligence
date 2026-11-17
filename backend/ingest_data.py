"""Run once after placing all source CSVs under backend sibling ../data/."""
from backend.rag_engine import ingest_all
if __name__=='__main__':
    result=ingest_all()
    print(f"Indexed {result['files']} CSV files, {result['rows']:,} rows and {result['chunks']:,} chunks")
