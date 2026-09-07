# Parallel research

Research uses an inspected website source URL when available, falling back to the project URL before inspection. This avoids restricting Wikipedia.com projects to the redirect domain when Wikipedia.org was inspected. It does not hardcode Wikipedia domains.

The product brief and audience guide the search objective. Queries target official help, search/navigation and user guides; an empty or fully rejected response triggers one broader help/documentation retry within the same domain. Errors remain distinct from zero accepted results. ResearchRunResult.attempts records destination, domain, objective, queries, returned count and accepted count (or an error).

Authored generation saves research-receipt.json beside research.json. Empty caches are searched again on a subsequent generation attempt; successful nonempty caches remain reusable. Existing videos are not silently rewritten.

Gemini ADK is instructed to cite relevant partner evidence only when it supports the copy. Its slide receipts include the cited partner sources. Final result.json includes research_evidence with accepted_source_count and distinct cited_partner_sources. Job progress reports both counts. This makes non-use visible rather than requiring decorative citations.

Live verification: artifacts/parallel-value-verification/report.md. Wikipedia returned four official help sources for both Spotlight and Short. Gemini cited Searching for Spotlight and Navigation for two Short scenes. The Short search scene used browser evidence alone. This is evidence of retrieval and use, not a measured quality uplift. No cloud deployment or MP4 re-render was part of this research retest.
