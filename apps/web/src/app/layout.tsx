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
  title: "DemoDirector",
  description: "Create polished, narrated product demos from a website and creative brief.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.className} ${inter.variable}`}><SessionBoundary>{children}</SessionBoundary></body>
    </html>
  );
}
