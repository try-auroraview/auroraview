import { cn } from '../lib/utils';
import { CATEGORIES, getSamplesByCategory } from '../data/samples';
import * as Icons from 'lucide-react';

interface SidebarProps {
  activeCategory: string | null;
  onCategoryClick: (categoryId: string) => void;
  onSettingsClick: () => void;
  onOpenLink: (url: string, title?: string) => void;
  onConsoleClick?: () => void;
  onExtensionsClick?: () => void;
  consoleOpen?: boolean;
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  rocket: Icons.Rocket,
  code: Icons.Code,
  layout: Icons.Layout,
  monitor: Icons.Monitor,
  box: Icons.Box,
  globe: Icons.Globe,
  brain: Icons.Brain,
};

export function Sidebar({ activeCategory, onCategoryClick, onSettingsClick, onOpenLink, onConsoleClick, onExtensionsClick, consoleOpen }: SidebarProps) {
  const samplesByCategory = getSamplesByCategory();

  const handleGitHubClick = () => {
    onOpenLink('https://github.com/try-auroraview/auroraview', 'GitHub - AuroraView');
  };

  return (
    <aside className="w-14 bg-card border-r border-border fixed h-screen flex flex-col items-center py-4">
      {/* Logo */}
      <div className="mb-6">
        <img
          src="./auroraview-logo.png"
          alt="AuroraView"
          className="w-9 h-9 rounded-lg object-contain"
        />
      </div>

      {/* Navigation icons */}
      <nav className="flex-1 flex flex-col items-center gap-1">
        {/* Home */}
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center transition-all",
            "text-muted-foreground hover:bg-accent hover:text-foreground",
            !activeCategory && "bg-primary/10 text-primary"
          )}
          title="Home"
        >
          <Icons.Home className="w-5 h-5" />
        </button>

        {/* Category icons */}
        {Object.entries(CATEGORIES).map(([catId, catInfo]) => {
          const Icon = iconMap[catInfo.icon] || Icons.Circle;
          const count = samplesByCategory[catId]?.length || 0;
          return (
            <button
              key={catId}
              onClick={() => onCategoryClick(catId)}
              className={cn(
                "w-10 h-10 rounded-lg flex items-center justify-center transition-all relative",
                "text-muted-foreground hover:bg-accent hover:text-foreground",
                activeCategory === catId && "bg-primary/10 text-primary"
              )}
              title={`${catInfo.title} (${count})`}
            >
              <Icon className="w-5 h-5" />
              {activeCategory === catId && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-primary rounded-r" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom icons */}
      <div className="flex flex-col items-center gap-1">
        {onConsoleClick && (
          <button
            onClick={onConsoleClick}
            className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center transition-all",
              "text-muted-foreground hover:bg-accent hover:text-foreground",
              consoleOpen && "bg-primary/10 text-primary"
            )}
            title="Process Console"
          >
            <Icons.Terminal className="w-5 h-5" />
          </button>
        )}
        {onExtensionsClick && (
          <button
            onClick={onExtensionsClick}
            className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center transition-all",
              "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
            title="Extensions"
          >
            <Icons.Puzzle className="w-5 h-5" />
          </button>
        )}
        <button
          onClick={handleGitHubClick}
          className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center transition-all",
            "text-muted-foreground hover:bg-accent hover:text-foreground"
          )}
          title="GitHub"
        >
          <Icons.Github className="w-5 h-5" />
        </button>
        <button
          onClick={onSettingsClick}
          className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center transition-all",
            "text-muted-foreground hover:bg-accent hover:text-foreground"
          )}
          title="Settings"
        >
          <Icons.Settings className="w-5 h-5" />
        </button>
      </div>
    </aside>
  );
}
