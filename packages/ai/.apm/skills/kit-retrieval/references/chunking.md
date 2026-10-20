# Chunking

Chunking decides what the retriever can find and what a citation can point
at. Choose boundaries from document structure, keep exact offsets, and measure
the effect on recall instead of copying a size from a blog post.

## Rules

- Chunk a normalized, versioned source. The chunk carries `source_id`,
  `source_version`, `tenant`, `acl`, `updated_at`, `section`, and exact
  `[start_char, end_char)` offsets into the normalized text.
- Keep the normalized text (or a hash of it) so `text[start:end]` can be
  re-verified at citation time; the template tests assert this property.
- Derive chunk ids deterministically from tenant, source, version and offsets.
  Re-indexing the same version is then an idempotent upsert, and stale
  versions are removable by version rather than by guessing.
- Copy the source access list onto every chunk. An empty access list is a
  data error, not "public".
- Never chunk across sources. A chunk with two owners has no correct access list.

## Strategies

| Strategy | When it fits | Cost |
| --- | --- | --- |
| Structure-aware (headings, paragraphs, sentences) | Manuals, policies, Markdown, HTML | Low; the default in [chunking.py.template](../assets/chunking.py.template) |
| Fixed windows with overlap | Unstructured plain text, transcripts | Lowest; cuts through sentences |
| Semantic (split where adjacent embeddings diverge) | Long narrative text without headings | Embedding calls at ingestion; harder to test |
| Parent-child (small chunks for matching, larger parent for context) | Precise matching but answers need context | Two granularities to keep consistent |
| Table and code aware | Spreadsheets, API references, source code | Format-specific parsers |
| Late chunking or contextual headers | Short chunks that lose context | Extra tokens per chunk |

## Sizing

- Start between 500 and 1500 characters for prose, measured in the unit your
  embedding model limits (tokens) and verified against that limit.
- Overlap of 10 to 20 percent avoids losing facts that straddle a boundary;
  the template overlaps whole sentences or paragraphs only, so overlap never
  starts mid-word.
- Prefix each chunk's embedding input with its section path when headings
  carry meaning ("Billing > Refunds"), while keeping `text` exactly the source
  span so offsets stay valid.
- Evaluate at least two sizes on the golden set; pick by recall at the `top_k`
  you actually send to the model, then by token cost.

## Normalization

Normalize before chunking and record the normalizer version in metadata:

- Convert to UTF-8, normalize line endings, and remove boilerplate (navigation,
  repeated headers and footers) that would dominate lexical scores.
- Preserve headings and list structure; they are the best boundaries.
- Extract tables to a readable row form rather than flattening cells.
- Strip secrets and personal data the index must not hold before chunking;
  redaction after indexing is too late for embeddings and caches.

## Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Citations point at the wrong text | Offsets computed on different text than stored | Chunk and store the same normalized text; test slicing |
| Duplicate hits for one fact | Excessive overlap or duplicate sources | Lower overlap; deduplicate by content hash at ingestion |
| Facts split across chunks are never found | No overlap, or boundaries ignore structure | Structure-aware splitting with bounded overlap |
| Old answers after an edit | New version indexed without removing the old | `retain_version` after a successful upsert |
| Chunk exceeds embedding limit | Size measured in characters only | Validate token counts with the model tokenizer |

## Verification

The [chunking tests](../assets/test_chunking.py.template) cover exact slicing,
heading paths, bounded overlap with forward progress, hard splits of oversized
words, deterministic version-scoped ids, access-list propagation, blank input,
and invalid policies. Add a fixture per document format you ingest.

## Sources

- [PostgreSQL text search parsers and dictionaries](https://www.postgresql.org/docs/current/textsearch-parsers.html)
- [LangChain text splitters](https://docs.langchain.com/oss/python/integrations/splitters)
- [LlamaIndex node parsers](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/)
- [OpenAI embeddings guide (input limits)](https://platform.openai.com/docs/guides/embeddings)
