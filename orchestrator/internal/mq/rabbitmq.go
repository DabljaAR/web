package mq

import (
	"fmt"
	"log"

	amqp "github.com/rabbitmq/amqp091-go"
)

// RabbitMQ holds the connection and channel
type RabbitMQ struct {
	Conn    *amqp.Connection
	Channel *amqp.Channel
}

// NewRabbitMQ initializes a connection to RabbitMQ
func NewRabbitMQ(url string) (*RabbitMQ, error) {
	conn, err := amqp.Dial(url)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to RabbitMQ: %w", err)
	}

	ch, err := conn.Channel()
	if err != nil {
		return nil, fmt.Errorf("failed to open a channel: %w", err)
	}

	// Declare the main exchange we will use for the pipeline
	err = ch.ExchangeDeclare(
		"dablja.jobs.exchange", // name
		"topic",                // type
		true,                   // durable
		false,                  // auto-deleted
		false,                  // internal
		false,                  // no-wait
		nil,                    // arguments
	)
	if err != nil {
		return nil, fmt.Errorf("failed to declare an exchange: %w", err)
	}

	log.Println("Successfully connected to RabbitMQ and declared exchange 'dablja.jobs.exchange'")
	return &RabbitMQ{
		Conn:    conn,
		Channel: ch,
	}, nil
}

// Close gracefully closes the connection and channel
func (r *RabbitMQ) Close() {
	if r.Channel != nil {
		r.Channel.Close()
	}
	if r.Conn != nil {
		r.Conn.Close()
	}
}
