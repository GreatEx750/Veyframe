"use client";

import { storyboardSchema, type Scene, type Storyboard } from "@demodirector/contracts";
import { useEffect, useState } from "react";

type StoryboardEditorProps = {
  projectId: string;
  initialStoryboard?: Storyboard;
};

export function StoryboardEditor({ projectId, initialStoryboard }: StoryboardEditorProps) {
  const [storyboard, setStoryboard] = useState<Storyboard | null>(initialStoryboard ?? null);
  const [message, setMessage] = useState(initialStoryboard ? "Storyboard ready" : "Loading storyboard…");
  const [busyScene, setBusyScene] = useState<string | null>(null);

  useEffect(() => {
    if (initialStoryboard) return;
    void fetch(`/api/projects/${projectId}/storyboard`, { cache: "no-store" })
      .then(async (response) => ({ response, body: await response.json() as unknown }))
      .then(({ response, body }) => {
        const parsed = storyboardSchema.safeParse(body);
        if (!response.ok || !parsed.success) throw new Error("Storyboard unavailable");
        setStoryboard(parsed.data);
        setMessage("Storyboard ready");
      })
      .catch(() => setMessage("Storyboard is not ready yet."));
  }, [initialStoryboard, projectId]);

  async function persist(scenes: Scene[]) {
    if (!storyboard) return;
    setMessage("Saving storyboard…");
    try {
      const response = await fetch(`/api/projects/${projectId}/storyboard`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_version: storyboard.version, scenes }),
      });
      const parsed = storyboardSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Save failed");
      setStoryboard(parsed.data);
      setMessage(`Saved version ${parsed.data.version}`);
    } catch {
      setMessage("Couldn’t save storyboard changes. Reload and try again.");
    }
  }

  function move(sceneIndex: number, offset: number) {
    if (!storyboard) return;
    const destination = sceneIndex + offset;
    if (destination < 0 || destination >= storyboard.scenes.length) return;
    const scenes = [...storyboard.scenes];
    const [scene] = scenes.splice(sceneIndex, 1);
    scenes.splice(destination, 0, scene);
    void persist(scenes);
  }

  function updateNarration(sceneId: string, narration: string) {
    if (!storyboard) return;
    setStoryboard({
      ...storyboard,
      scenes: storyboard.scenes.map((scene) => scene.id === sceneId ? { ...scene, narration } : scene),
    });
  }

  function deleteScene(sceneId: string) {
    if (!storyboard) return;
    void persist(storyboard.scenes.filter((scene) => scene.id !== sceneId));
  }

  function addScene() {
    if (!storyboard || storyboard.scenes.length === 0) return;
    const template = storyboard.scenes.at(-1)!;
    const scene: Scene = {
      ...template,
      id: `scene-${Date.now()}`,
      title: "New scene",
      objective: "Describe this scene",
      narration: "Add narration for this scene.",
      duration_seconds: 10,
    };
    void persist([...storyboard.scenes, scene]);
  }

  async function regenerate(sceneId: string) {
    setBusyScene(sceneId);
    setMessage("Regenerating selected scene…");
    try {
      const response = await fetch(
        `/api/projects/${projectId}/storyboard/scenes/${sceneId}/regenerate`,
        { method: "POST" },
      );
      const parsed = storyboardSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Regeneration failed");
      setStoryboard(parsed.data);
      setMessage(`Regenerated one scene · version ${parsed.data.version}`);
    } catch {
      setMessage("Couldn’t regenerate this scene.");
    } finally {
      setBusyScene(null);
    }
  }

  if (!storyboard) {
    return <main className="storyboard-page"><p role="status">{message}</p></main>;
  }

  return (
    <main className="storyboard-page">
      <header className="storyboard-header">
        <div><span className="step-pill">Review</span><h1>Review your storyboard</h1><p>Reorder, refine, or regenerate one scene before recording.</p></div>
        <div className="storyboard-summary"><b>{storyboard.scenes.length} scenes</b><span>{storyboard.total_duration_seconds.toFixed(0)} seconds</span><span>Version {storyboard.version}</span></div>
      </header>
      <section aria-label="Storyboard scenes" className="storyboard-list">
        {storyboard.scenes.map((scene, index) => (
          <article className="storyboard-card" key={scene.id}>
            <div className="scene-order"><b>{index + 1}</b><button aria-label={`Move ${scene.title} up`} disabled={index === 0} onClick={() => move(index, -1)} type="button">↑</button><button aria-label={`Move ${scene.title} down`} disabled={index === storyboard.scenes.length - 1} onClick={() => move(index, 1)} type="button">↓</button></div>
            <div className="storyboard-thumbnail"><span>Scene preview</span><time>{scene.duration_seconds.toFixed(0)}s</time></div>
            <div className="storyboard-copy"><h2>{scene.title}</h2><p>{scene.objective}</p><label htmlFor={`narration-${scene.id}`}>Narration</label><textarea id={`narration-${scene.id}`} onBlur={() => void persist(storyboard.scenes)} onChange={(event) => updateNarration(scene.id, event.target.value)} value={scene.narration} /></div>
            <div className="storyboard-actions"><button disabled={busyScene === scene.id} onClick={() => void regenerate(scene.id)} type="button">{busyScene === scene.id ? "Regenerating…" : "Regenerate"}</button><button className="danger-button" onClick={() => deleteScene(scene.id)} type="button">Delete</button></div>
          </article>
        ))}
      </section>
      <footer className="storyboard-footer"><button onClick={addScene} type="button">＋ Add simple scene</button><p role="status">{message}</p></footer>
    </main>
  );
}
