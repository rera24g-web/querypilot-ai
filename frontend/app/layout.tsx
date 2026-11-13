import "./globals.css";
export const metadata = { title: "QueryPilot AI", description: "Autonomous product analytics agent" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body>{children}</body></html>);
}
