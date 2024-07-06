success=0
throttled=0

for i in {1..10}; do
    sleep 0.1
    response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/a" \
    -H "X-User-ID: jeff" \
    -H "X-Forwarded-For: 127.0.0.1")
    
    if [ $response -eq 200 ]; then
        ((success++))
    elif [ $response -eq 429 ]; then
        ((throttled++))
    fi
done

echo "Successful requests: $success"
echo "Throttled requests: $throttled"