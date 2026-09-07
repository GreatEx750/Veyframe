"use client";

import { projectSchema, type Project } from "@demodirector/contracts";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ProductNavigation } from "@/components/product-navigation";
import { isJudgeDemoProject, JUDGE_DEMO_VIDEO_URL } from "@/lib/judge-demo";

type SortMode = "updated" | "name" | "duration";

const statusLabels: Record<Project["status"], string> = {
  draft: "Draft",
  storyboarding: "Storyboarding",
  ready: "Ready",
  capturing: "Capturing",
  editing: "Editing",
  rendering: "Rendering",
  published: "Published",
  failed: "Failed",
};

function durationLabel(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

function updatedLabel(value: string) {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  const hours = Math.floor(elapsed / 3_600_000);
  if (hours < 1) return "Edited just now";
  if (hours < 24) return `Edited ${hours}h ago`;
  return `Edited ${Math.floor(hours / 24)}d ago`;
}

export function DemoLibrary() {
  const { replace } = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sort, setSort] = useState<SortMode>("updated");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const [videoFailures, setVideoFailures] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    let active = true;
    fetch("/api/projects", { cache: "no-store" })
      .then(async (response) => {
        if (response.status === 401) {
          replace("/login?reason=session_expired");
          return [];
        }
        if (!response.ok) throw new Error("Project library could not be loaded.");
        return projectSchema.array().parse(await response.json());
      })
      .then((items) => {
        if (active) setProjects(items);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Project library could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [replace]);

  const visibleProjects = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return projects
      .filter((project) => {
        const matchesQuery =
          !normalized ||
          project.name.toLowerCase().includes(normalized) ||
          project.product_summary.toLowerCase().includes(normalized);
        const matchesStatus = statusFilter === "all" || project.status === statusFilter;
        return matchesQuery && matchesStatus;
      })
      .sort((left, right) => {
        if (sort === "name") return left.name.localeCompare(right.name);
        if (sort === "duration") return right.requested_duration_seconds - left.requested_duration_seconds;
        return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
      });
  }, [projects, query, sort, statusFilter]);

  const published = projects.filter((project) => project.status === "published").length;
  const activeProjects = projects.filter((project) => !["published", "failed"].includes(project.status)).length;
  const totalMinutes = Math.round(projects.reduce((sum, project) => sum + project.requested_duration_seconds, 0) / 60);

  async function deleteProject(project: Project) {
    const confirmed = window.confirm(
      `Delete “${project.name}”? This removes the project from your library and cannot be undone.`,
    );
    if (!confirmed) return;
    setDeletingProjectId(project.id);
    setNotice(null);
    try {
      const response = await fetch(`/api/projects/${project.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Project deletion failed");
      setProjects((current) => current.filter((item) => item.id !== project.id));
      setNotice({ kind: "success", message: `${project.name} deleted.` });
    } catch {
      setNotice({ kind: "error", message: `Couldn’t delete ${project.name}. Try again.` });
    } finally {
      setDeletingProjectId(null);
    }
  }

  return (
    <main className="library-shell">
      <ProductNavigation active="projects" />

      <section className="library-main">
        <header className="library-heading">
          <div><h1>Projects</h1><p>Create, manage, and publish your product demos.</p></div>
          <Link className="library-new" href="/studio">+ New demo</Link>
        </header>

        <section className="library-summary" aria-label="Library summary">
          <span><strong>{projects.length}</strong> projects</span>
          <span><strong>{published}</strong> published</span>
          <span><strong>{activeProjects}</strong> active</span>
          <span><strong>{totalMinutes}m</strong> total runtime</span>
        </section>

        <div className="library-content-head">
          <div className="library-section-title"><h2>Recent demos</h2><span>{visibleProjects.length} shown</span></div>
          <div className="library-controls">
            <label><span>⌕</span><input aria-label="Search demos" placeholder="Search demos" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
            <select aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              <option value="draft">Draft</option>
              <option value="rendering">Rendering</option>
              <option value="published">Published</option>
              <option value="failed">Failed</option>
            </select>
            <select aria-label="Sort demos" value={sort} onChange={(event) => setSort(event.target.value as SortMode)}>
              <option value="updated">Last edited</option>
              <option value="name">Name</option>
              <option value="duration">Duration</option>
            </select>
          </div>
        </div>

        {notice && <p className={`library-notice ${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>{notice.message}</p>}

        {loading && <p className="library-state" role="status">Loading your demos…</p>}
        {error && <p className="library-state error" role="alert">{error}</p>}
        {!loading && !error && visibleProjects.length === 0 && (
          <div className="library-empty"><b>No demos found</b><p>Try another search or create a new demo.</p></div>
        )}
        <section className="demo-card-grid" aria-label="Demo projects">
          {visibleProjects.map((project, index) => (
            <article className="demo-card" key={project.id}>
              <Link className="demo-card-link" href={`/projects/${project.id}/editor`}>
                <div className={`demo-thumbnail demo-thumbnail-${index % 4} ${project.status === "published" ? "has-video" : ""}`}>
                  {project.status === "published" && !videoFailures.has(project.id) ? <>
                    <video
                      aria-label={`Preview ${project.name}`}
                      muted
                      onError={() => setVideoFailures((current) => new Set(current).add(project.id))}
                      playsInline
                      preload="metadata"
                      src={isJudgeDemoProject(project.id) ? JUDGE_DEMO_VIDEO_URL : `/api/projects/${project.id}/exports/latest/video`}
                    />
                    <span className="video-ready">▶ Video ready</span>
                  </> : project.status === "published" ? <>
                    <span>Video unavailable</span>
                  </> : <span>{project.name.slice(0, 2).toUpperCase()}</span>}
                  <time>{durationLabel(project.requested_duration_seconds)}</time>
                </div>
                <div className="demo-card-body">
                  <h3>{project.name}</h3>
                  <p><i className={`status-dot status-${project.status}`} />{statusLabels[project.status]} <span>{({presentation_demo: "Presentation", product_demo: "Product", spotlight_demo: "Spotlight", short_demo: "Short"})[project.demo_mode]}</span></p>
                </div>
              </Link>
              <footer>
                <span>{updatedLabel(project.updated_at)}</span>
                <button aria-label={`Delete ${project.name}`} disabled={deletingProjectId === project.id} onClick={() => void deleteProject(project)} type="button">{deletingProjectId === project.id ? "Deleting…" : "Delete"}</button>
              </footer>
            </article>
          ))}
        </section>
      </section>
    </main>
  );
}
