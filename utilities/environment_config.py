import os

document_index_name = "movies"
document_file_location = "../data/movies.json"
es_client_endpoint = os.environ.get("elastic_client")
es_user_id = os.environ.get("elastic_user_id")
es_password = os.environ.get("elastic_password")

es_embedding_inference_id="vllm-embedding-service"
es_generative_inference_id="vllm-inference-service"

ec_client_timeout = 5000

embedding_dimensions = 4096
embedding_model_endpoint = os.environ.get("embedding_model_endpoint")
embedding_model_name = os.environ.get("embedding_model_name")
embedding_model_api_key = os.environ.get("embedding_model_api_key")

generative_model_endpoint = os.environ.get("generative_model_endpoint")
generative_model_name = os.environ.get("generative_model_name")
generative_model_api_key = os.environ.get("generative_model_api_key")

rerank_model_endpoint = os.environ.get("rerank_model_endpoint")
rerank_model_name = os.environ.get("rerank_model_name")
rerank_model_api_key = os.environ.get("rerank_model_api_key")