import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ThemeProvider } from "@/components/providers/theme-provider";
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={inter.variable}>
      <body className="min-h-screen bg-surface-0 antialiased">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
          <QueryProvider>
            {children}
            <Toaster
              theme="dark"
              position="bottom-right"
              toastOptions={{
                style: {
                  background: "rgba(15, 22, 18, 0.95)",
                  border: "1px solid rgba(82, 183, 136, 0.2)",
                  color: "#e2e8e4",
                },
              }}
            />
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
