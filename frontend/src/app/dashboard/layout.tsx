export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="h-screen w-full bg-surface text-foreground overflow-hidden">
            {children}
        </div>
    );
}
