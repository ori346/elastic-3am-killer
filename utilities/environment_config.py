import os

document_index_name = "movies"
document_file_location = "../data/movies.json"

embedding_dimensions = 4096
embedding_model_endpoint = os.environ.get("embedding_model_endpoint")
embedding_model_name = os.environ.get("embedding_model_name")
embedding_model_api_key = os.environ.get("embedding_model_api_key")

generative_model_endpoint = os.environ.get("generative_model_endpoint")
generative_model_name = os.environ.get("generative_model_name")
generative_model_api_key = os.environ.get("generative_model_api_key")
