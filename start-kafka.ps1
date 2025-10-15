$JAVA = "C:\jdk\jdk-25\bin\java.exe"
$KAFKA_HOME = "C:\kafka\kafka_2.12-3.7.0"

Write-Host "Starting Kafka Server..." -ForegroundColor Green

& $JAVA `
  -cp "$KAFKA_HOME\libs\*" `
  "-Dkafka.logs.dir=$KAFKA_HOME\logs" `
  "-Dlog4j.configuration=file:$KAFKA_HOME\config\log4j.properties" `
  kafka.Kafka "$KAFKA_HOME\config\server.properties"