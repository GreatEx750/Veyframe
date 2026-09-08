import Link from "next/link";
import Image from "next/image";

import { LogoutButton } from "@/components/logout-button";

type ProductNavigationProps = {
  active: "projects" | "studio" | "jobs";
};

const iconPaths = {
  jobs: "M5 4h14v16H5V4Zm4 5h6m-6 4h6m-6 4h3",
  projects: "M4 6h6l2 2h8v11H4V6Z",
  studio: "M7 5h10l3 4v10H4V9l3-4Zm2 5v4l4-2-4-2Z",
};

function NavigationIcon({ name }: { name: keyof typeof iconPaths }) {
  return <svg aria-hidden="true" className="icon" viewBox="0 0 24 24"><path d={iconPaths[name]} /></svg>;
}

export function ProductNavigation({ active }: ProductNavigationProps) {
  return (
    <aside className="navigation product-navigation">
      <Link aria-label="Veyframe projects" className="wordmark" href="/projects"><Image src="/brand/veyframe-icon.png" width={28} height={28} alt="" /><b>Veyframe</b></Link>
      <nav aria-label="Primary navigation">
        <Link aria-current={active === "projects" ? "page" : undefined} className={`nav-item ${active === "projects" ? "active" : ""}`} href="/projects" title="Projects"><NavigationIcon name="projects" /><span>Projects</span></Link>
        <Link aria-current={active === "studio" ? "page" : undefined} className={`nav-item ${active === "studio" ? "active" : ""}`} href="/studio" title="Studio"><NavigationIcon name="studio" /><span>Studio</span></Link>
        <Link aria-current={active === "jobs" ? "page" : undefined} className={`nav-item ${active === "jobs" ? "active" : ""}`} href="/jobs" title="Jobs"><NavigationIcon name="jobs" /><span>Jobs</span></Link>
      </nav>
      <LogoutButton navigation />
    </aside>
  );
}
