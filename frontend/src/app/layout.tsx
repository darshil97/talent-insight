import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Talent Insight",
  description: "An evidence-based recruiting assistant. Currently in development.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
