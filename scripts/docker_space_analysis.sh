#!/bin/bash
# =============================================================================
# Docker Space Analysis Script for CEX Arbitrage System
# =============================================================================
# This script analyzes Docker storage consumption and identifies cleanup opportunities
# Run this on the production server to understand Docker space usage

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==============================================================================${NC}"
echo -e "${BLUE}DOCKER SPACE ANALYSIS FOR CEX ARBITRAGE SYSTEM${NC}"
echo -e "${BLUE}==============================================================================${NC}"

# Function to print section headers
print_section() {
    echo -e "\n${YELLOW}$1${NC}"
    echo "----------------------------------------"
}

# Function to convert bytes to human readable
bytes_to_human() {
    local bytes=$1
    if [[ $bytes -ge 1073741824 ]]; then
        echo "$(echo "scale=2; $bytes / 1073741824" | bc)GB"
    elif [[ $bytes -ge 1048576 ]]; then
        echo "$(echo "scale=2; $bytes / 1048576" | bc)MB"
    elif [[ $bytes -ge 1024 ]]; then
        echo "$(echo "scale=2; $bytes / 1024" | bc)KB"
    else
        echo "${bytes}B"
    fi
}

# =============================================================================
# 1. OVERALL DOCKER SYSTEM ANALYSIS
# =============================================================================
print_section "1. DOCKER SYSTEM OVERVIEW"

if command -v docker &> /dev/null; then
    echo "Docker version:"
    docker version --format "{{.Server.Version}}" 2>/dev/null || echo "Docker daemon not accessible"
    
    echo -e "\nDocker system disk usage:"
    docker system df 2>/dev/null || echo "Failed to get Docker system info"
    
    echo -e "\nDetailed Docker system disk usage:"
    docker system df -v 2>/dev/null || echo "Failed to get detailed Docker system info"
else
    echo -e "${RED}Docker not found or not accessible${NC}"
fi

# =============================================================================
# 2. CONTAINER ANALYSIS
# =============================================================================
print_section "2. RUNNING CONTAINERS ANALYSIS"

if docker ps &> /dev/null; then
    echo "Currently running containers:"
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Size}}"
    
    echo -e "\nAll containers (including stopped):"
    docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Size}}"
    
    echo -e "\nContainer resource usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" 2>/dev/null || echo "Failed to get container stats"
else
    echo -e "${RED}Cannot access Docker containers${NC}"
fi

# =============================================================================
# 3. IMAGE ANALYSIS
# =============================================================================
print_section "3. DOCKER IMAGES ANALYSIS"

if docker images &> /dev/null; then
    echo "Docker images:"
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    
    echo -e "\nDangling images (not tagged and not referenced by containers):"
    dangling_images=$(docker images -f "dangling=true" -q)
    if [[ -n "$dangling_images" ]]; then
        docker images -f "dangling=true" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
        
        # Calculate total size of dangling images
        total_dangling_size=0
        for image in $dangling_images; do
            size=$(docker image inspect "$image" --format='{{.Size}}' 2>/dev/null || echo 0)
            total_dangling_size=$((total_dangling_size + size))
        done
        echo -e "\nTotal dangling images size: $(bytes_to_human $total_dangling_size)"
    else
        echo "No dangling images found"
    fi
    
    echo -e "\nUnused images (not referenced by any container):"
    unused_images=$(docker image ls --filter "dangling=false" --format "{{.ID}}" | while read image; do
        if [[ -z "$(docker ps -a --filter ancestor="$image" --format="{{.ID}}")" ]]; then
            echo "$image"
        fi
    done)
    
    if [[ -n "$unused_images" ]]; then
        echo "$unused_images" | while read image; do
            docker images --filter "reference=$image" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
        done
    else
        echo "No unused images found"
    fi
else
    echo -e "${RED}Cannot access Docker images${NC}"
fi

# =============================================================================
# 4. VOLUME ANALYSIS
# =============================================================================
print_section "4. DOCKER VOLUMES ANALYSIS"

if docker volume ls &> /dev/null; then
    echo "Docker volumes:"
    docker volume ls
    
    echo -e "\nVolume details:"
    docker volume ls --format "{{.Name}}" | while read volume; do
        size=$(docker run --rm -v "$volume":/data alpine sh -c "du -sh /data 2>/dev/null | cut -f1" 2>/dev/null || echo "Unknown")
        mountpoint=$(docker volume inspect "$volume" --format='{{.Mountpoint}}' 2>/dev/null || echo "Unknown")
        echo "Volume: $volume, Size: $size, Mountpoint: $mountpoint"
    done
    
    echo -e "\nUnused volumes:"
    unused_volumes=$(docker volume ls -q --filter "dangling=true")
    if [[ -n "$unused_volumes" ]]; then
        echo "$unused_volumes"
        
        # Calculate total size of unused volumes
        total_unused_size=0
        echo "$unused_volumes" | while read volume; do
            size_kb=$(docker run --rm -v "$volume":/data alpine sh -c "du -sk /data 2>/dev/null | cut -f1" 2>/dev/null || echo 0)
            size_bytes=$((size_kb * 1024))
            echo "Unused volume: $volume, Size: $(bytes_to_human $size_bytes)"
        done
    else
        echo "No unused volumes found"
    fi
else
    echo -e "${RED}Cannot access Docker volumes${NC}"
fi

# =============================================================================
# 5. DOCKER OVERLAY2 STORAGE ANALYSIS
# =============================================================================
print_section "5. DOCKER STORAGE DRIVER ANALYSIS"

# Check Docker storage driver
storage_driver=$(docker info --format '{{.Driver}}' 2>/dev/null || echo "unknown")
echo "Storage driver: $storage_driver"

if [[ "$storage_driver" == "overlay2" ]]; then
    # Find Docker root directory
    docker_root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
    echo "Docker root directory: $docker_root"
    
    if [[ -d "$docker_root" ]]; then
        echo -e "\nDocker directory sizes:"
        sudo du -sh "$docker_root"/* 2>/dev/null | sort -hr || echo "Cannot access Docker directory (requires sudo)"
        
        if [[ -d "$docker_root/overlay2" ]]; then
            echo -e "\nOverlay2 directory analysis:"
            overlay_size=$(sudo du -sh "$docker_root/overlay2" 2>/dev/null | cut -f1 || echo "Unknown")
            echo "Total overlay2 size: $overlay_size"
            
            echo -e "\nTop 10 largest overlay2 directories:"
            sudo du -sh "$docker_root/overlay2"/* 2>/dev/null | sort -hr | head -10 || echo "Cannot analyze overlay2 directories"
        fi
        
        if [[ -d "$docker_root/containers" ]]; then
            echo -e "\nContainer logs analysis:"
            container_logs_size=$(sudo du -sh "$docker_root/containers" 2>/dev/null | cut -f1 || echo "Unknown")
            echo "Total container logs size: $container_logs_size"
            
            echo -e "\nLargest container log files:"
            sudo find "$docker_root/containers" -name "*.log" -exec du -sh {} \; 2>/dev/null | sort -hr | head -10 || echo "Cannot analyze container logs"
        fi
    fi
fi

# =============================================================================
# 6. NETWORK ANALYSIS
# =============================================================================
print_section "6. DOCKER NETWORKS ANALYSIS"

if docker network ls &> /dev/null; then
    echo "Docker networks:"
    docker network ls
    
    echo -e "\nUnused networks:"
    docker network prune --dry-run 2>/dev/null || echo "Cannot check for unused networks"
else
    echo -e "${RED}Cannot access Docker networks${NC}"
fi

# =============================================================================
# 7. BUILD CACHE ANALYSIS
# =============================================================================
print_section "7. DOCKER BUILD CACHE ANALYSIS"

if docker buildx version &> /dev/null; then
    echo "Build cache usage:"
    docker buildx du 2>/dev/null || echo "Cannot access build cache info"
else
    echo "Docker Buildx not available, checking legacy build cache"
fi

# =============================================================================
# 8. CLEANUP RECOMMENDATIONS
# =============================================================================
print_section "8. CLEANUP RECOMMENDATIONS"

echo -e "${GREEN}Safe cleanup commands (will ask for confirmation):${NC}"
echo "1. Remove dangling images:"
echo "   docker image prune"
echo ""
echo "2. Remove unused volumes:"
echo "   docker volume prune"
echo ""
echo "3. Remove unused networks:"
echo "   docker network prune"
echo ""
echo "4. Remove unused containers:"
echo "   docker container prune"
echo ""
echo "5. Remove build cache:"
echo "   docker buildx prune"
echo ""

echo -e "${YELLOW}Aggressive cleanup (use with caution):${NC}"
echo "6. Remove all unused Docker objects:"
echo "   docker system prune -a"
echo ""
echo "7. Remove all stopped containers, unused networks, dangling images, and build cache:"
echo "   docker system prune -a --volumes"
echo ""

echo -e "${RED}Nuclear option (DESTROYS EVERYTHING):${NC}"
echo "8. Complete Docker reset (WARNING: This will remove ALL Docker data):"
echo "   docker system prune -a --volumes --force"
echo "   sudo rm -rf /var/lib/docker/overlay2/*"
echo ""

# =============================================================================
# 9. MONITORING COMMANDS
# =============================================================================
print_section "9. MONITORING COMMANDS"

echo "Continuous monitoring commands:"
echo "1. Watch Docker system usage:"
echo "   watch 'docker system df'"
echo ""
echo "2. Monitor container resource usage:"
echo "   docker stats"
echo ""
echo "3. Monitor disk usage:"
echo "   watch 'df -h'"
echo ""

echo -e "\n${BLUE}Analysis complete. Review the output above for cleanup opportunities.${NC}"
echo -e "${YELLOW}IMPORTANT: Always backup critical data before running cleanup commands!${NC}"