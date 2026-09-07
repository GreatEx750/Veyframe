"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KeyboardEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";

import styles from "./landing-page.module.css";
import { GenerationBenchmark } from "./generation-benchmark";

const formats = [
  { id: "presentation", label: "Presentations", title: "A presentation with the product in action.",
    duration: "20-second excerpt", example: "/examples/northstar-presentation-20s.mp4" },
  { id: "product", label: "Product demos", title: "See a product story come to life.",
    duration: "20 seconds", example: "/examples/northstar-product-20s.mp4" },
  { id: "spotlight", label: "Spotlights", title: "One feature. A moment in the spotlight.",
    duration: "30 seconds", example: "/landing/spotlight-example.mp4" },
  { id: "short", label: "Shorts", title: "A little time. A whole product story.",
    duration: "45 seconds", example: "/landing/short-example.mp4?v=rounded-3" },
] as const;

function subscribeToMotion(callback: () => void) {
  const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
  preference.addEventListener("change", callback);
  return () => preference.removeEventListener("change", callback);
}

function motionPreference() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function PlayIcon({ paused = true }: { paused?: boolean }) {
  return <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    {paused ? <path d="M7 4.5a1 1 0 0 1 1.5-.86l12 7.5a1 1 0 0 1 0 1.72l-12 7.5A1 1 0 0 1 7 19.5Z" />
      : <path d="M6 5h4v14H6zm8 0h4v14h-4z" />}
  </svg>;
}

export function LandingPage() {
  const router = useRouter();
  const [judgeLoading, setJudgeLoading] = useState(false);
  const [judgeError, setJudgeError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [paused, setPaused] = useState(false);
  const [failed, setFailed] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const reducedMotion = useSyncExternalStore(subscribeToMotion, motionPreference, () => true);
  const video = useRef<HTMLVideoElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const format = formats[selected];
  const poster = `/landing/${format.id === "short" ? "short-google-rounded" : format.id}-poster.jpg`;
  const previewSource = `/landing/${format.id}-preview.mp4${format.id === "short" ? "?v=rounded-3" : ""}`;
  const playing = !paused && !reducedMotion && !dialogOpen;
  const [manualPlay, setManualPlay] = useState(false);
  const shouldPlay = playing || (manualPlay && !paused && !dialogOpen);

  useEffect(() => {
    const element = video.current;
    if (!element) return;
    let active = true;
    const sync = () => {
      if (shouldPlay && !document.hidden) {
        void element.play().catch(() => { if (active) setPaused(true); });
      } else element.pause();
    };
    sync();
    document.addEventListener("visibilitychange", sync);
    return () => {
      active = false;
      element.pause();
      document.removeEventListener("visibilitychange", sync);
    };
  }, [selected, shouldPlay]);

  function choose(index: number) {
    setFailed(false);
    setSelected(index);
  }

  function navigateTabs(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    if (event.key === "ArrowRight") next = (index + 1) % formats.length;
    else if (event.key === "ArrowLeft") next = (index + formats.length - 1) % formats.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = formats.length - 1;
    else return;
    event.preventDefault();
    choose(next);
    tabs.current[next]?.focus();
  }

  function openExample() {
    setDialogOpen(true);
    dialog.current?.showModal();
  }

  async function enterJudgeDemo() {
    if (judgeLoading) return;
    setJudgeLoading(true);
    setJudgeError(null);
    try {
      const response = await fetch("/api/auth/judge-session", { method: "POST" });
      if (!response.ok) throw new Error("Judge demo is temporarily unavailable. Please try again.");
      router.replace("/projects");
      router.refresh();
    } catch {
      setJudgeError("Judge demo is temporarily unavailable. Please try again.");
    } finally {
      setJudgeLoading(false);
    }
  }

  return <div className={styles.landing}>
    <a className={styles.skipLink} href="#landing-main">Skip to content</a>
    <header className={styles.header}>
      <nav className={styles.navigation} aria-label="Site navigation">
        <Link className={styles.brand} href="/" aria-label="Veyframe home">
          <span className={styles.brandIcon}><Image src="/brand/veyframe-icon.png" width={32} height={32} alt="" priority /></span>
          <span>veyframe</span>
        </Link>
        <div className={styles.accountLinks}>
          <Link href="/login">Log in</Link>
          <Link className={styles.signup} href="/signup">Sign up</Link>
        </div>
      </nav>
    </header>

    <main className={styles.main} id="landing-main">
      <section className={styles.introduction} aria-labelledby="landing-heading">
        <h1 id="landing-heading">Turn what you do into a story worth watching.</h1>
        <p>Veyframe turns your website into videos. Recorded, narrated, and ready to share.</p>
        <div className={styles.primaryActions}>
          <Link className={styles.getStarted} href="/signup">Get started</Link>
          <button className={styles.judgeDemo} disabled={judgeLoading} onClick={enterJudgeDemo} type="button">
            {judgeLoading ? "Opening demo…" : "Judge Demo Mode"}
          </button>
        </div>
        {judgeError && <p className={styles.judgeError} role="alert">{judgeError}</p>}
        <span className={styles.ctaNote}>Your website. Your brief. Your next video.</span>
      </section>

      <section className={styles.showcase} aria-label="Videos made with Veyframe">
        <div className={styles.tabs} role="tablist" aria-label="Video formats">
          {formats.map((item, index) => <button key={item.id}
            aria-controls="format-preview" aria-selected={selected === index}
            className={styles.tab} id={`format-${item.id}`} role="tab"
            ref={(element) => { tabs.current[index] = element; }}
            tabIndex={selected === index ? 0 : -1} type="button"
            onClick={() => choose(index)} onKeyDown={(event) => navigateTabs(event, index)}>
            {item.label}
          </button>)}
        </div>

        <div className={styles.preview} data-format={format.id} role="tabpanel" id="format-preview"
          aria-labelledby={`format-${format.id}`} tabIndex={0}>
          <video key={format.id} ref={video} aria-label={`${format.label} preview`}
            autoPlay={shouldPlay} muted playsInline preload="metadata"
            poster={poster} src={previewSource}
            onError={() => setFailed(true)}
            onEnded={() => {
              if (shouldPlay && !reducedMotion) choose((selected + 1) % formats.length);
              else setPaused(true);
            }} />
          {!failed && <button className={styles.playback} type="button"
            aria-label={shouldPlay ? "Pause preview" : "Play preview"}
            onClick={() => { setManualPlay(true); setPaused(shouldPlay); }}>
            <PlayIcon paused={!shouldPlay} />
          </button>}
          {failed && <div className={styles.previewError} role="alert">
            <p>Preview couldn’t load.</p><a href={format.example}>Open the example video</a>
          </div>}
        </div>

        <button className={styles.watchDemo} onClick={openExample} type="button">
          <span className={styles.thumbnail} data-format={format.id}>
            <Image src={poster} width={168} height={96} alt="" />
            <span><PlayIcon /></span>
          </span>
          <span className={styles.watchCopy}>
            <strong>{format.title}</strong>
            <span>Watch with sound <span aria-hidden="true">↗</span><small>{format.duration}</small></span>
          </span>
        </button>
        <p className={styles.exampleNote}>Actual videos made with Veyframe. Select a format to explore.</p>
      </section>
      <GenerationBenchmark />
    </main>

    <footer className={styles.footer}>
      <span>Veyframe</span><span>Make your next story a moving one.</span>
      <Link href="/studio">Open Studio <span aria-hidden="true">↗</span></Link>
    </footer>

    <dialog className={styles.demoDialog} ref={dialog} aria-labelledby="example-title"
      onClose={() => setDialogOpen(false)}
      onClick={(event) => { if (event.target === event.currentTarget) dialog.current?.close(); }}>
      <div className={styles.dialogContent}>
        <header><div><h2 id="example-title">{format.label}</h2><p>{format.duration} · Made with Veyframe</p></div>
          <button type="button" aria-label="Close example" onClick={() => dialog.current?.close()}>×</button>
        </header>
        {dialogOpen && <video key={format.id} aria-label={`${format.label} full example`}
          src={format.example} poster={poster} controls autoPlay playsInline />}
      </div>
    </dialog>
  </div>;
}
