#!/bin/bash
# OPD 项目管理便捷脚本

OPD_URL="http://localhost:8765"

case "$1" in
  list-projects)
    curl -s "$OPD_URL/api/projects"
    ;;
  list-stories)
    curl -s "$OPD_URL/api/stories?project_id=$2"
    ;;
  create-story)
    curl -s -X POST "$OPD_URL/api/stories" \
      -H "Content-Type: application/json" \
      -d "{\"project_id\": $2, \"title\": \"$3\", \"raw_input\": \"$4\"}"
    ;;
  story-status)
    curl -s "$OPD_URL/api/stories/$2"
    ;;
  confirm)
    curl -s -X POST "$OPD_URL/api/stories/$2/confirm"
    ;;
  reject)
    curl -s -X POST "$OPD_URL/api/stories/$2/reject"
    ;;
  stream)
    curl -s -N "$OPD_URL/api/stories/$2/stream"
    ;;
  *)
    echo "Usage: $0 {list-projects|list-stories|create-story|story-status|confirm|reject|stream}"
    echo ""
    echo "Examples:"
    echo "  $0 list-projects"
    echo "  $0 list-stories 6"
    echo "  $0 create-story 6 '用户登录' '需要一个简单的用户名密码登录功能'"
    echo "  $0 story-status 8"
    echo "  $0 confirm 8"
    echo "  $0 stream 8"
    ;;
esac
