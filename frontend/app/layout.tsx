import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { QueryProvider } from "@/components/providers/query-provider";
import { Toaster } from "sonner";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "DevReview AI — AI-Powered Code Review",
    template: "%s | DevReview AI",
  },
  description:
    "AI-powered code review platform for developers. Analyse repositories, review pull requests, and track technical debt.",
  keywords: ["code review", "AI", "developer tools", "GitHub", "security", "code quality"],
  openGraph: {
    title: "DevReview AI",
    description: "AI-powered code review platform",
    type: "website",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#000000",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable}`}>
      <body className="min-h-screen bg-surface-0 antialiased">
        <QueryProvider>
          {children}
          <Toaster
            theme="dark"
            position="top-center"
            toastOptions={{
              style: {
                background: "#111114",
                border: "1px solid #26262c",
                color: "#f4f4f5",
              },
            }}
          />
        </QueryProvider>
      </body>
    </html>
  );
}
