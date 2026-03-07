import type { Metadata } from "next";
import { Providers } from "@/components/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "HireRight AI - First Hire Compliance Made Simple",
  description:
    "AI-powered labor law compliance assistant for US small business owners. Get state-specific checklists, worker classification analysis, and employee handbooks.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
