import "./globals.css";
import type { Metadata } from "next";
import { Sidebar } from "@/components/Sidebar";
import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "Spirits Wiki",
  description: "Private lore wiki for the Spirits fictional world",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[var(--color-wiki-bg)]">
        <AuthProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 p-6 max-w-5xl">{children}</main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
