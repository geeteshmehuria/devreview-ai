import { AuthProvider } from "@/components/providers/auth-provider";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { MobileNav } from "@/components/layout/mobile-nav";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <div className="min-h-screen bg-surface-0 flex">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          {/* Bottom padding on phones keeps content clear of the fixed tab bar */}
          <main className="flex-1 px-4 pt-5 pb-28 sm:px-6 sm:pt-6 lg:p-8">{children}</main>
        </div>
      </div>
      <MobileNav />
    </AuthProvider>
  );
}
