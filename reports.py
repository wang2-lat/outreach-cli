from typing import Dict, Optional

def generate_weekly_report(db, days: int = 7) -> Dict:
    posts = db.get_posts_by_date_range(days)
    
    if not posts:
        return {
            'total_posts': 0,
            'total_clicks': 0,
            'total_conversions': 0,
            'avg_ctr': 0,
            'by_platform': [],
            'top_posts': []
        }
    
    total_clicks = sum(p['clicks'] for p in posts)
    total_conversions = sum(p['conversions'] for p in posts)
    avg_ctr = (total_conversions * 100.0 / total_clicks) if total_clicks > 0 else 0
    
    platform_stats = {}
    for post in posts:
        platform = post['platform']
        if platform not in platform_stats:
            platform_stats[platform] = {
                'platform': platform,
                'posts': 0,
                'clicks': 0,
                'conversions': 0
            }
        
        platform_stats[platform]['posts'] += 1
        platform_stats[platform]['clicks'] += post['clicks']
        platform_stats[platform]['conversions'] += post['conversions']
    
    by_platform = []
    for platform, stats in platform_stats.items():
        avg_ctr = (stats['conversions'] * 100.0 / stats['clicks']) if stats['clicks'] > 0 else 0
        by_platform.append({**stats, 'avg_ctr': avg_ctr})
    
    by_platform.sort(key=lambda x: x['avg_ctr'], reverse=True)
    top_posts = sorted(posts, key=lambda x: x['clicks'], reverse=True)
    
    return {
        'total_posts': len(posts),
        'total_clicks': total_clicks,
        'total_conversions': total_conversions,
        'avg_ctr': avg_ctr,
        'by_platform': by_platform,
        'top_posts': top_posts
    }

def suggest_template(db, platform: Optional[str] = None) -> Optional[Dict]:
    posts = db.get_posts_by_date_range(30)
    
    if not posts:
        return None
    
    if platform:
        posts = [p for p in posts if p['platform'].lower() == platform.lower()]
    
    if not posts:
        return None
    
    best_post = max(posts, key=lambda x: x['clicks'])
    
    if best_post['clicks'] == 0:
        return None
    
    platform_performance = {}
    for post in posts:
        p = post['platform']
        if p not in platform_performance:
            platform_performance[p] = {'clicks': 0, 'count': 0}
        platform_performance[p]['clicks'] += post['clicks']
        platform_performance[p]['count'] += 1
    
    best_platform = max(
        platform_performance.items(),
        key=lambda x: x[1]['clicks'] / x[1]['count']
    )[0]
    
    high_performers = [p for p in posts if p['clicks'] > 0]
    avg_title_length = sum(len(p['title']) for p in high_performers) / len(high_performers) if high_performers else 0
    
    pattern = f"Posts with ~{int(avg_title_length)} characters perform well"
    
    return {
        'best_platform': best_platform,
        'pattern': pattern,
        'example_title': best_post['title'],
        'example_clicks': best_post['clicks'],
        'example_ctr': best_post['ctr'] if best_post['ctr'] else 0
    }
