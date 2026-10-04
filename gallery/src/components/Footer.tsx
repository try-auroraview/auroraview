import { cn } from '../lib/utils';
import * as Icons from 'lucide-react';

export function Footer() {
  return (
    <footer className={cn(
      "mt-16 pt-6 border-t border-border/50",
      "bg-gradient-to-t from-background/50 to-transparent"
    )}>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-5">
          <span className="font-medium">AuroraView Gallery</span>
          <a
            href="https://github.com/try-auroraview/auroraview"
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "flex items-center gap-1.5 transition-colors",
              "hover:text-primary"
            )}
          >
            <Icons.Github className="w-3.5 h-3.5" />
            GitHub
          </a>
          <a
            href="https://github.com/try-auroraview/auroraview/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-primary transition-colors"
          >
            Report Issue
          </a>
        </div>
        <div className="flex items-center gap-2">
          <Icons.Scale className="w-3 h-3" />
          MIT License
        </div>
      </div>
    </footer>
  );
}
