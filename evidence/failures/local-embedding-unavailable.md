# Local embedding baseline unavailable

The requested provider was `BAAI/bge-small-zh-v1.5`. Model files were present in the local Hugging Face cache and the experiment was attempted offline.

`sentence-transformers` imports failed through Transformers with:

`ModuleNotFoundError: No module named 'torch.distributed.tensor.device_mesh'`

Installed versions were sentence-transformers 5.5.1, Transformers 5.9.0, and Torch 2.4.1. `memory_garden.providers.local_embedding` consequently set `HAS_SENTENCE_TRANSFORMERS` to false and `_local_embedding_registry()` returned no registry. No embedding metric is approved.
