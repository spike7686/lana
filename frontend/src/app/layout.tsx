import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lana Project",
  description: "Crypto data warehouse dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
