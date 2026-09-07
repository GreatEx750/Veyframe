import type { Metadata } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";

import "./styles.css";
import "./studio.css";
import { SessionBoundary } from "@/components/session-boundary";

const inter = Inter({
  display: "swap",
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Veyframe — Turn what you do into a story",
  description: "Turn your website into narrated product videos, presentations, spotlights, and shorts with real recordings and a creative brief.",
  icons: { icon: "/brand/veyframe-icon.png" },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.className} ${inter.variable}`}><SessionBoundary>{children}</SessionBoundary></body>
    </html>
  );
}
