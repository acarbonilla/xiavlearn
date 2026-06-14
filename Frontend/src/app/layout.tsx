import type { Metadata } from "next";

import Header from "@/components/Header";

import "./globals.css";

export const metadata: Metadata = {
  title: "XiAv Learn",
  description: "AI-powered personalized English learning",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <Header />
        {children}
      </body>
    </html>
  );
}
