import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/layout/providers";
import { SIDEBAR_SCRIPT } from "@/lib/sidebar-rail";

export const metadata: Metadata = {
  title: "Wingman — Cluster Management",
  description: "OpenShift HostedControlPlane lifecycle management platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="h-full antialiased">
      <head>
        {/* The sidebar's stored width, on <html> before the first paint (lib/sidebar-rail.ts) */}
        <script dangerouslySetInnerHTML={{ __html: SIDEBAR_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
