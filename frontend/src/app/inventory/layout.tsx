export default function InventoryLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="h-screen w-full bg-[#0a0a0b] text-white overflow-hidden">
            {children}
        </div>
    );
}
