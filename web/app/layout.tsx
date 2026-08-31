import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { Sidebar } from "@/components/sidebar";

import "./globals.css";

// Two weights only, per the visual language: never 600 or 700.
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "LedgerProof",
  description: "Settlement reconciliation for Razorpay merchants.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="min-w-0 flex-1 px-10 py-10 lg:px-16">
            <div className="mx-auto max-w-content">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
