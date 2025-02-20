import os
from collections.abc import Iterator
from dotenv import load_dotenv

from datachain import DataChain, C, File, DataModel

from unstructured.partition.api import partition_via_api
from unstructured.cleaners.core import clean
from unstructured.cleaners.core import replace_unicode_quotes
from unstructured.cleaners.core import group_broken_paragraphs
from unstructured.embed.huggingface import (
    HuggingFaceEmbeddingConfig,
    HuggingFaceEmbeddingEncoder,
)

load_dotenv()


# Define the output as a DataModel class
class Chunk(DataModel):
    key: str
    text: str
    embeddings: list[float]


# Define embedding encoder

embedding_encoder = HuggingFaceEmbeddingEncoder(config=HuggingFaceEmbeddingConfig())


# Use signatures to define UDF input/output (these can be pydantic model or regular Python types)
def process_pdf(file: File) -> Iterator[Chunk]:
    # Ingest the file
    with file.open() as f:

        chunks = partition_via_api(
            file=f,
            metadata_filename=file.path,
            api_key=os.getenv("UNSTRUCTURED_API_KEY"),
            api_url=os.getenv("UNSTRUCTURED_API_URL"),
            content_type="pdf",
            strategy="fast",
            chunking_strategy="by_title",
        )

    # Clean the chunks and add new columns
    for chunk in chunks:
        chunk.apply(
            lambda text: clean(
                text, bullets=True, extra_whitespace=True, trailing_punctuation=True
            )
        )
        chunk.apply(replace_unicode_quotes)
        chunk.apply(group_broken_paragraphs)

    # create embeddings
    chunks_embedded = embedding_encoder.embed_documents(chunks)

    # Add new rows to DataChain
    for chunk in chunks_embedded:
        yield Chunk(
            key=file.path,
            text=chunk.text,
            embeddings=chunk.embeddings,
        )


dc = (
    DataChain.from_storage("gs://datachain-demo/neurips")
    .settings(parallel=-1)
    .filter(C.file.path.glob("*/1987/*.pdf"))
    .gen(document=process_pdf)
)

dc.save("embedded-documents")

DataChain.from_dataset("embedded-documents").show()
